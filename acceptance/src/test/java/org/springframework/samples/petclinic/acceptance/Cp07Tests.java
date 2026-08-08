package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** registration-date: When no registration date is supplied, set it to the server's current date and return 'reg... */
@Tag("cp07")
class Cp07Tests extends AcceptanceBase {

	@Test
	void coreDefaultsToToday() throws Exception {
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.registrationDate").value(today()));
	}

	@Test
	void functionalityKeepsSuppliedDate() throws Exception {
		ObjectNode o = ownerNode();
		o.put("registrationDate", "2020-06-15");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.registrationDate").value("2020-06-15"));
	}
}
