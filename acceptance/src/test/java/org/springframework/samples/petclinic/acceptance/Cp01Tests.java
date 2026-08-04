package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp01 required-fields: Reject creating an owner that is missing or blank in any of firstName, lastName, address,... */
@Tag("cp01")
class Cp01Tests extends AcceptanceBase {

	@Test
	void errorRejectsMissingCity() throws Exception {
		ObjectNode o = ownerNode();
		o.remove("city");
		createOwner(o).andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.errors").value(org.hamcrest.Matchers.hasItem("city")));
	}

	@Test
	void errorRejectsBlankTelephone() throws Exception {
		ObjectNode o = ownerNode();
		o.put("telephone", "   ");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityAcceptsCompleteOwner() throws Exception {
		createOwner(ownerNode()).andExpect(status().is2xxSuccessful());
	}
}
