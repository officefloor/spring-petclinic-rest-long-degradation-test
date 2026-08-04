package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp27 contact-preference: Return 'contactPreference' = 'EMAIL' when an email is present, otherwise 'PHONE'.... */
@Tag("cp27")
class Cp27Tests extends AcceptanceBase {

	@Test
	void corePhoneWhenNoEmail() throws Exception {
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.contactPreference").value("PHONE"));
	}

	@Test
	void functionalityEmailWhenPresent() throws Exception {
		ObjectNode o = ownerNode();
		o.put("email", uniqueEmail());
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.contactPreference").value("EMAIL"));
	}
}
