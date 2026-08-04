package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp58 risk-flag: Return 'riskFlag' true when any of these hold: the owner is a possible duplicate, the emai... */
@Tag("cp58")
class Cp58Tests extends AcceptanceBase {

	@Test
	void coreRiskFlagFalseNormally() throws Exception {
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(jsonPath("$.riskFlag").value(false));
	}
}
