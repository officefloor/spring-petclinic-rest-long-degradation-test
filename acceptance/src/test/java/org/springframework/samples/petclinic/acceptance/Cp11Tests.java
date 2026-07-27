package org.springframework.samples.petclinic.acceptance;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp11: default registrationDate to today when not supplied. */
@Tag("cp11")
class Cp11Tests extends AcceptanceBase {

	@Test
	void coreDefaultsRegistrationDateToToday() throws Exception {
		int id = createOwnerOk(validOwner());
		getOwner(id).andExpect(jsonPath("$.registrationDate").exists())
				.andExpect(content().string(containsString(today())));
	}

	@Test
	void functionalityKeepsSuppliedRegistrationDate() throws Exception {
		ObjectNode o = validOwner();
		o.put("registrationDate", "2001-02-03");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(content().string(containsString("2001-02-03")));
	}
}
